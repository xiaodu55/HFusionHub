package com.hfusionhub.mapper;

import com.baomidou.mybatisplus.core.mapper.BaseMapper;
import com.hfusionhub.entity.FeatureFlag;
import org.apache.ibatis.annotations.Mapper;

@Mapper
public interface FeatureFlagMapper extends BaseMapper<FeatureFlag> {
}
