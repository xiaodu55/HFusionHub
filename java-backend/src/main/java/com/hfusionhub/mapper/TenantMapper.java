package com.hfusionhub.mapper;

import com.baomidou.mybatisplus.core.mapper.BaseMapper;
import com.hfusionhub.entity.Tenant;
import org.apache.ibatis.annotations.Mapper;
import org.apache.ibatis.annotations.Param;

import java.util.List;

@Mapper
public interface TenantMapper extends BaseMapper<Tenant> {

    Tenant selectBySlug(@Param("slug") String slug);

    List<Tenant> selectByUserId(@Param("userId") Long userId);
}
